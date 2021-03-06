from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from .models import Category, Expense
from preferences.models import UserPreference
import datetime
import json
import csv
import xlsxwriter
import xlwt
from django.db.models import Sum
from django.template.loader import get_template
from xhtml2pdf import pisa


def search_expenses(request):
    if request.method == "POST":
        keyword = json.loads(request.body).get("searchText")
        expenses = (
            Expense.objects.filter(amount__istartswith=keyword, owner=request.user)
            | Expense.objects.filter(date__startswith=keyword, owner=request.user)
            | Expense.objects.filter(description__icontains=keyword, owner=request.user)
            | Expense.objects.filter(category__icontains=keyword, owner=request.user)
        )
        data = expenses.values()

        return JsonResponse(list(data), safe=False)


@login_required(login_url="/auth/login")
def index(request):
    expenses = Expense.objects.filter(owner=request.user).order_by("-date")
    paginator = Paginator(expenses, 6)
    page_no = request.GET.get("page")
    page_object = Paginator.get_page(paginator, page_no)
    currency = None
    if UserPreference.objects.filter(user=request.user).exists():
        currency = UserPreference.objects.get(user=request.user).currency
    context = {"expenses": expenses, "page_object": page_object, "currency": currency}
    return render(request, "expenses/index.html", context)


@login_required(login_url="/auth/login")
def add_expense(request):
    categories = Category.objects.all()
    context = {"categories": categories, "values": request.POST}

    if request.method == "GET":
        return render(request, "expenses/add_expense.html", context)

    if request.method == "POST":
        amount = request.POST["amount"]
        description = request.POST["description"]
        category = request.POST["category"]
        date = request.POST["date"]

        if not amount:
            messages.error(request, "Amount is required.")
            return render(request, "expenses/add_expense.html", context)
        if not description:
            messages.error(request, "Description is required.")
            return render(request, "expenses/add_expense.html", context)
        if not category:
            messages.error(request, "Category is required.")
            return render(request, "expenses/add_expense.html", context)

        Expense.objects.create(
            owner=request.user,
            amount=amount,
            date=date,
            category=category,
            description=description,
        )
        messages.success(request, "Expense saved successfully.")

        return render(request, "expenses/add_expense.html")


def edit_expense(request, id):
    expense = Expense.objects.get(pk=id)
    categories = Category.objects.all()
    context = {"expense": expense, "categories": categories}

    if request.method == "GET":
        return render(request, "expenses/edit-expense.html", context)

    if request.method == "POST":
        amount = request.POST["amount"]
        description = request.POST["description"]
        category = request.POST["category"]
        date = request.POST["date"]

        if not amount:
            messages.error(request, "Amount is required.")
            return render(request, "expenses/add_expense.html", context)
        if not description:
            messages.error(request, "Description is required.")
            return render(request, "expenses/add_expense.html", context)
        if not category:
            messages.error(request, "Category is required.")
            return render(request, "expenses/add_expense.html", context)
        if not date:
            date = datetime.date.today()

        expense.owner = request.user
        expense.amount = amount
        expense.date = date
        expense.category = category
        expense.description = description
        expense.save()

        messages.success(request, "Expense updated successfully.")
        return redirect("expenses:index")


def delete_expense(request, id):
    expense = Expense.objects.get(pk=id)
    context = {"expense": expense}
    if request.method == "POST":
        expense.delete()
        messages.success(request, "Expense deleted successfully.")
        return redirect("expenses:index")

    return render(request, "expenses/delete_expense.html", context)


def expense_summary(request):
    todays_date = datetime.date.today()
    six_months_before = todays_date - datetime.timedelta(days=30*6)
    expenses = Expense.objects.filter(date__gte=six_months_before, date__lte=todays_date, owner=request.user)
    result = {}

    def get_category(expense):
        return expense.category

    category_list = list(set(map(get_category, expenses)))

    def get_expense_category_amount(category):
        amount = 0
        filtered_by_category = expenses.filter(category=category)

        for item in filtered_by_category:
            amount += item.amount

        return amount

    for expense in expenses:
        for category in category_list:
            result[category] = get_expense_category_amount(category)

    return JsonResponse({'expense_summary': result}, safe=False)


def get_monthly_expense_summary(request):
    current_month = datetime.date.today().month
    result = {}
    check_month = current_month

    i = 1
    while i <= 6:
        if check_month == 0:
            check_month = 12
        expenses = Expense.objects.filter(date__month=check_month, owner=request.user)
        month_expense = 0
        for expense in expenses:
            month_expense += expense.amount
        datetime_obj = datetime.datetime.strptime(str(check_month), '%m')
        key_month = datetime_obj.strftime('%B')
        # result[key_month] = month_expense
        result[i] = {
                "month": key_month,
                "amount": month_expense
            }
        check_month -= 1
        i += 1


    # expenses = Expense.objects.filter(date__month=current_month, owner=request.user)
    # current_month_expense = 0
    # for expense in expenses:
    #     current_month_expense += expense.amount
    return JsonResponse({'expense_summary': result}, safe=False)


def view_expense_summary(request):
    return render(request, 'expenses/expense-summary.html')


def export_csv(request):
    response = HttpResponse(content_type='text/csv')
    filename = 'Expenses' + str(datetime.datetime.now()) + '.csv'
    response['Content-Disposition'] = 'attachment; filename=' + filename

    writer = csv.writer(response)
    writer.writerow(['Amount', 'Description', 'Category', 'Date'])

    expenses = Expense.objects.filter(owner=request.user)

    for expense in expenses:
        writer.writerow([expense.amount, expense.description, expense.category, expense.date])

    return response


def export_excel(request):
    response = HttpResponse(content_type='application/ms-excel')
    filename = 'Expenses' + datetime.datetime.now().strftime('%d%m%Y%H%M%S') + '.xlsx'
    response['Content-Disposition'] = 'attachment; filename=' + filename

    workbook = xlwt.Workbook(encoding='utf-8')
    worksheet = workbook.add_sheet('Expense')
    font_style = xlwt.XFStyle()
    font_style.font.bold = True

    columns = ["Amount", "Description", "Category", "Date"]
    for col_num in range(len(columns)):
        worksheet.write(0, col_num, columns[col_num], font_style)

    expenses = Expense.objects.filter(owner=request.user)

    row = 1

    for expense in expenses:
        worksheet.write(row, 0, expense.amount)
        worksheet.write(row, 1, expense.description)
        worksheet.write(row, 2, expense.category)
        worksheet.write(row, 3, expense.date)
        row += 1

    workbook.save(response)

    return response


def export_pdf(request):
    template_path = 'expenses/pdf_output.html'
    expenses = Expense.objects.filter(owner=request.user)
    sum = expenses.aggregate(Sum('amount'))
    context = {
        'expenses': expenses,
        'total': sum['amount__sum']
    }
    # Create a Django response object, and specify content_type as pdf
    response = HttpResponse(content_type='application/pdf')
    filename = 'Expenses' + datetime.datetime.now().strftime('%d%m%Y%H%M%S') + '.pdf'
    response['Content-Disposition'] = 'attachment; filename=' + filename
    # find the template and render it.
    template = get_template(template_path)
    html = template.render(context)

    # create a pdf
    pisa_status = pisa.CreatePDF(
       html, dest=response)
    # if error then show some funy view
    if pisa_status.err:
       return HttpResponse('We had some errors <pre>' + html + '</pre>')
    return response